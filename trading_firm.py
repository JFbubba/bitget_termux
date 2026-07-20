#!/usr/bin/env python3
"""trading_firm.py — Firme de trading multi-agents AUTONOME (12 rôles TradingAgents,
arXiv 2412.20138). Jumeau runtime des sous-agents `.claude/agents/*.md`.

Classement : SAFE. Lecture seule + LLM ; AUCUN ordre, aucun secret, aucune dépendance
nouvelle (réutilise `llm_agent`, ERR-004). Ne touche JAMAIS le consensus ni les murs.

Pipeline par symbole (fidèle au papier) :
  4 analystes (local) → débat bull⇄bear (local) → research-manager (cloud) →
  trader (cloud) → débat risque agressif/neutre/conservateur (local) → risk-judge (cloud)
  → FirmDecision structurée.

Objectif CONCRET (mesure-d'abord, §92) : tourner seule sur cron, décider par symbole, et
JOURNALISER son ombre `firm_shadow` (jugée net-de-frais par le même audit IC que les 14).
Elle ne pèse sur l'argent QUE via la 19ᵉ voix opt-in (`firm_agent.py`), gated OFF, armée
délibérément après preuve d'edge — jamais silencieusement (cf. voice_shadow_measure.py).

Répartition backend hybride (tunable .env) : analystes + débatteurs = Ollama LOCAL (volume) ;
les 3 juges décisifs = Gemini CLOUD (raisonnement), avec cap coût dur + repli local.

CLI :
  python trading_firm.py --status            # CONSULTATION (lit le cache, AUCUN appel LLM)
  python trading_firm.py --symbol BTCUSDT     # une décision (coûteux : LLM)
  python trading_firm.py --cycle              # tout l'univers (coûteux : LLM ; usage cron)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from config_utils import cfg as _cfg
from config_utils import load_env as _load_env

ROOT = Path(__file__).resolve().parent
DECISIONS = ROOT / ".firm_decisions.json"        # cache par symbole (dashboard + 19ᵉ voix)
OVERLAY = ROOT / ".overlay_votes.jsonl"           # ombre firm_shadow (mesurée par live_ic_audit)
META = ROOT / "firm_voice_meta.json"              # méta pour voice_shadow_measure (wf_edge n/a)
CLOUD_LOG = ROOT / ".firm_cloud_calls.json"       # compteur jour des appels cloud (cap coût)

# rating 5 crans <-> direction (échelle du papier : Buy/Overweight/Hold/Underweight/Sell)
RATINGS = {"Buy": 1.0, "Overweight": 0.5, "Hold": 0.0, "Underweight": -0.5, "Sell": -1.0}
HARD_WALL_USDT = 50.0                              # mur ABSOLU futures/trade (jamais dépassé)


def _knob(name, default):
    """.env PRIORITAIRE (armable sans toucher config.py) sinon config sinon défaut."""
    v = os.getenv(name)
    return v if v is not None else _cfg(name, default)


def enabled():
    """Interrupteur maître de la firme autonome (défaut OFF). OFF -> cycle() est un no-op.
    C'est la MESURE d'ombre (SAFE, hors chemin-argent) ; distinct de FIRM_AGENT_ENABLED
    (la voix qui pèse sur le consensus)."""
    v = str(os.getenv("FIRM_ENABLED", "")).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("FIRM_ENABLED", False))


def _kill_switched():
    return (ROOT / "KILL_SWITCH").exists()


# ---------------------------------------------------------------- données internes
def _snap(symbol):
    """Features de prix compactes (réutilise llm_agent — aucun secret/solde/position)."""
    try:
        import llm_agent
        return llm_agent._snapshot(symbol)
    except Exception:
        return None


def _state(symbol):
    """Blocs internes du bot via le dashboard lecture seule (localhost). {} si indispo —
    la firme dégrade alors sur le seul snapshot de prix (fail-open)."""
    try:
        import urllib.request
        url = f"http://127.0.0.1:8787/api/state?symbol={symbol}&tf=5m"
        with urllib.request.urlopen(url, timeout=float(_knob("FIRM_STATE_TIMEOUT_S", 6))) as r:
            d = json.loads(r.read().decode())
        return d.get("state", d) if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------- routage LLM + cap coût
def _cloud_ok():
    """True tant que le cap journalier d'appels cloud n'est pas atteint (fail-closed coût)."""
    cap = int(float(_knob("FIRM_MAX_CLOUD_CALLS_PER_DAY", 120)))
    day = time.strftime("%Y-%m-%d")
    try:
        d = json.loads(CLOUD_LOG.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return int(d.get(day, 0)) < cap


def _cloud_inc():
    day = time.strftime("%Y-%m-%d")
    try:
        d = json.loads(CLOUD_LOG.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    try:
        CLOUD_LOG.write_text(json.dumps({day: int(d.get(day, 0)) + 1}), encoding="utf-8")
    except Exception:
        pass


def _call(prompt, kind, timeout):
    """Un appel LLM. kind='judge' -> Gemini cloud (si clé + budget), sinon Ollama local.
    Réutilise la plomberie de llm_agent (coût cloud journalisé par _call_gemini)."""
    import llm_agent
    want_cloud = (kind == "judge"
                  and str(_knob("FIRM_LLM_JUDGE_BACKEND", "gemini")).lower() == "gemini"
                  and os.getenv("GEMINI_API_KEY") and _cloud_ok())
    if want_cloud:
        try:
            model = str(_knob("FIRM_LLM_JUDGE_MODEL", "gemini-2.5-flash"))
            txt = llm_agent._call_gemini(prompt, model, timeout)
            _cloud_inc()
            return txt
        except Exception:
            pass                                  # repli local (fail-open, jamais de blocage)
    model = str(_knob("FIRM_LLM_LOCAL_MODEL", "qwen2.5:1.5b"))
    return llm_agent._call_local(prompt, model, timeout)


def _json(prompt, kind):
    """Appel LLM -> dict parsé, ou None (fail-safe total : timeout/erreur/JSON illisible)."""
    timeout = float(_knob("FIRM_JUDGE_TIMEOUT_S" if kind == "judge" else "FIRM_LOCAL_TIMEOUT_S",
                          20.0 if kind == "judge" else 30.0))
    try:
        txt = _call(prompt, kind, timeout)
    except Exception:
        return None
    try:
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            return None
        obj = json.loads(txt[i:j + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _num(obj, key, lo, hi, default=None):
    """Extrait obj[key] comme float clampé [lo,hi], ou default."""
    try:
        v = float(obj.get(key))
        return max(lo, min(hi, v))
    except Exception:
        return default


def _compact(x, n=1400):
    """Sérialise un bloc de données en bornant la taille (contrôle des tokens)."""
    try:
        return json.dumps(x, default=str)[:n]
    except Exception:
        return "{}"


# ---------------------------------------------------------------- les 12 rôles
def _analyst(role, instruction, data):
    p = (f"Tu es l'analyste {role} d'une firme de trading crypto (perp Bitget). {instruction} "
         "Horizon : prochaines heures à jours. Sois factuel, pas d'opinion gratuite.\n"
         f"Données internes du bot (aucun secret) :\n{_compact(data)}\n"
         'Réponds STRICTEMENT en JSON compact : '
         '{"bias": <-1..1>, "confidence": <0..1>, "note": "<14 mots max>"}')
    r = _json(p, "analyst")
    if not r:
        return None
    b = _num(r, "bias", -1, 1)
    if b is None:
        return None
    return {"bias": round(b, 3), "confidence": round(_num(r, "confidence", 0, 1, 0.3), 3),
            "note": str(r.get("note", ""))[:80]}


def _researcher(side, reports, last_opp):
    who = "HAUSSIER (Bull)" if side == "bull" else "BAISSIER (Bear)"
    adv = "baissier" if side == "bull" else "haussier"
    p = (f"Tu es l'analyste {who} d'une firme de trading crypto. Construis un argument fondé "
         "sur les preuves des rapports d'analystes, et RÉPONDS au dernier argument adverse "
         "(ne le ré-énumère pas). Garde en tête que les frais (~6 bps/côté) mangent l'edge.\n"
         f"Rapports analystes : {_compact(reports)}\n"
         f"Dernier argument {adv} : {str(last_opp)[:400]}\n"
         'Réponds STRICTEMENT en JSON : {"argument": "<45 mots max>", "lean": <-1..1>}')
    r = _json(p, "debate") or {}
    # voix muette -> lean None = EXCLUE de l'agrégat (jamais un vote neutre 0.0 fantôme),
    # symétrique de _analyst qui renvoie None quand le biais manque.
    return {"argument": str(r.get("argument", ""))[:300],
            "lean": _num(r, "lean", -1, 1)}


def _manager(reports, bull, bear):
    p = ("Tu es le Manager de recherche (juge du débat directionnel). Pèse la force des "
         "arguments bull/bear et TRANCHE. Échelle EXACTE (un cran) : Buy/Overweight/Hold/"
         "Underweight/Sell. Hold = équilibre réel des preuves OU edge attendu < frais "
         "(mesure-d'abord). Cite l'argument décisif.\n"
         f"Rapports : {_compact(reports)}\nBull : {_compact(bull, 500)}\nBear : {_compact(bear, 500)}\n"
         'Réponds STRICTEMENT en JSON : {"rating": "<un cran>", "direction": <-1..1>, '
         '"rationale": "<30 mots max>"}')
    r = _json(p, "judge") or {}
    rating = r.get("rating") if r.get("rating") in RATINGS else None
    return {"rating": rating, "direction": _num(r, "direction", -1, 1),
            "rationale": str(r.get("rationale", ""))[:200]}


def _trader(plan, reports):
    p = ("Tu es l'Agent Trader. Convertis le plan en proposition PAPER (jamais un ordre). "
         "Action : Buy/Hold/Sell. Ancre-toi dans les rapports. Sizing SOUS les murs (mur dur "
         "50 $/trade, levier ×5). Si l'edge ne couvre pas ~6 bps/côté -> Hold.\n"
         f"Plan : {_compact(plan, 500)}\nRapports : {_compact(reports, 900)}\n"
         'Réponds STRICTEMENT en JSON : {"action": "Buy|Hold|Sell", "direction": <-1..1>, '
         '"sizing_usdt": <0..50>, "reasoning": "<25 mots max>"}')
    r = _json(p, "judge") or {}
    return {"action": r.get("action", "Hold"), "direction": _num(r, "direction", -1, 1),
            "sizing_usdt": _num(r, "sizing_usdt", 0, HARD_WALL_USDT, 0.0),
            "reasoning": str(r.get("reasoning", ""))[:200]}


def _risk(profile, trader, reports, last_a, last_c):
    label = {"aggressive": "Agressif (haut rendement/risque, dans les murs)",
             "neutral": "Neutre (équilibré, corrélation réelle)",
             "conservative": "Conservateur (protège le capital, incarne les murs)"}[profile]
    p = (f"Tu es l'analyste de risque {label} d'une firme crypto. Évalue la proposition du "
         "trader et RÉPONDS aux arguments adverses. Rappel : les murs (50/250, ×5, stop −5 %) "
         "sont ABSOLUS ; un plaidoyer agressif = au mieux +1 palier de notional SOUS les murs.\n"
         f"Proposition trader : {_compact(trader, 400)}\nRapports : {_compact(reports, 700)}\n"
         f"Dernier agressif : {str(last_a)[:250]}\nDernier conservateur : {str(last_c)[:250]}\n"
         'Réponds STRICTEMENT en JSON : {"argument": "<40 mots max>", "lean": <-1..1>}')
    r = _json(p, "debate") or {}
    return {"argument": str(r.get("argument", ""))[:250], "lean": _num(r, "lean", -1, 1)}


def _risk_debate_enabled():
    """§105 — débat de risque LOCAL gaté, défaut OFF. MESURE (20/07, cache réel 8 symboles,
    24 appels) : 29 % de voix muettes, 88 % de complaisance (« le trader a raison »),
    similarité MÉDIANE 1,00 entre les voix qui parlent (8/12 paires quasi-identiques).
    Les 3 voix ne sont pas un débat mais un ÉCHO de la proposition du trader : les compter
    comme 3 signaux triple-pondère le trader dans le repli de `_assemble` et pollue l'ombre
    firm_shadow. Un modèle plus capable les fait diverger (qwen2.5:7b -> similarité 0,22,
    0 % muet, 0 % complaisant) mais coûte 78 s/appel sur ce VPS (2 cœurs, pas de GPU) contre
    un timeout de 30 s : inexploitable ici. Réarmable en un levier le jour d'un vrai modèle."""
    return str(_knob("FIRM_RISK_DEBATE", 0)).strip().lower() in ("1", "true", "yes", "on")


def _risk_round(trader, reports):
    """Les 3 voix de risque (agressif -> conservateur -> neutre, chacune voyant les
    précédentes). OFF -> 3 voix EXCLUES (lean None) sans aucun appel LLM."""
    if not _risk_debate_enabled():
        muet = {"argument": "", "lean": None}
        return {p: dict(muet) for p in ("aggressive", "conservative", "neutral")}
    agg = _risk("aggressive", trader, reports, "", "")
    con = _risk("conservative", trader, reports, agg.get("argument", ""), "")
    neu = _risk("neutral", trader, reports, agg.get("argument", ""), con.get("argument", ""))
    return {"aggressive": agg, "conservative": con, "neutral": neu}


def _risk_judge(plan, trader, risk_debate):
    p = ("Tu es le Portfolio Manager / Juge du risque : DÉCISION FINALE. Synthétise le débat "
         "de risque + le plan + la proposition trader. Pèse la QUALITÉ de preuve (méfie-toi de "
         "la confiance rhétorique). Échelle EXACTE (un cran) : Buy/Overweight/Hold/Underweight/"
         "Sell. Sizing final SOUS les murs (mur dur 50 $/trade). net_of_fees_ok=false si l'edge "
         "attendu ne couvre pas ~6 bps/côté (-> Hold).\n"
         f"Plan : {_compact(plan, 400)}\nTrader : {_compact(trader, 300)}\n"
         # débat OFF/muet -> on le DIT au juge plutôt que de lui servir des voix vides
         # (qui l'inviteraient à broder un consensus inexistant).
         + (f"Débat risque : {_compact(risk_debate, 800)}\n"
            if any((v or {}).get("lean") is not None for v in risk_debate.values())
            else "Débat risque : indisponible — tranche sur le plan et la proposition seuls.\n")
         +
         'Réponds STRICTEMENT en JSON : {"rating": "<un cran>", "direction": <-1..1>, '
         '"conviction": <0..1>, "sizing_usdt": <0..50>, "horizon": "<court|moyen>", '
         '"net_of_fees_ok": <true|false>, "thesis": "<30 mots max>"}')
    r = _json(p, "judge") or {}
    rating = r.get("rating") if r.get("rating") in RATINGS else None
    return {"rating": rating, "direction": _num(r, "direction", -1, 1),
            "conviction": _num(r, "conviction", 0, 1), "horizon": str(r.get("horizon", "court"))[:20],
            "sizing_usdt": _num(r, "sizing_usdt", 0, HARD_WALL_USDT),
            "net_of_fees_ok": bool(r.get("net_of_fees_ok", False)),
            "thesis": str(r.get("thesis", ""))[:200]}


# ---------------------------------------------------------------- assemblage + pipeline
def _dir_to_rating(d):
    if d >= 0.6:
        return "Buy"
    if d >= 0.2:
        return "Overweight"
    if d <= -0.6:
        return "Sell"
    if d <= -0.2:
        return "Underweight"
    return "Hold"


def _assemble(symbol, snap, reports, bull, bear, plan, trader, risk_debate, verdict):
    """Décision finale ROBUSTE : le juge tranche s'il a répondu, sinon repli déterministe
    sur la moyenne des signaux disponibles (la firme émet toujours une décision si ≥2
    analystes ont répondu)."""
    sigs = []
    for r in reports.values():
        if r and r.get("bias") is not None:
            sigs.append(r["bias"])
    for x in (bull, bear, plan, trader, verdict, *risk_debate.values()):
        for k in ("lean", "direction"):
            v = (x or {}).get(k)
            if isinstance(v, (int, float)):
                sigs.append(float(v))
    mean = sum(sigs) / len(sigs) if sigs else 0.0
    direction = verdict.get("direction")
    if direction is None:
        direction = round(mean, 3)
    conviction = verdict.get("conviction")
    if conviction is None:
        conviction = round(min(1.0, abs(direction)), 3)
    rating = verdict.get("rating") or _dir_to_rating(direction)
    default_notional = float(_knob("FUTURES_AUTO_NOTIONAL_USDT", 10))
    sizing = verdict.get("sizing_usdt")
    if sizing is None:
        sizing = default_notional
    sizing = max(0.0, min(float(sizing), HARD_WALL_USDT))          # mur ABSOLU
    nof = verdict.get("net_of_fees_ok")
    if nof is None:
        nof = abs(direction) >= 0.3 and conviction >= 0.3
    price = (snap or {}).get("last")
    return {
        "symbol": symbol, "ts": int(time.time()), "price": price,
        "rating": rating, "direction": round(float(direction), 3),
        "conviction": round(float(conviction), 3),
        "sizing_suggested_usdt": round(sizing, 2), "horizon": verdict.get("horizon", "court"),
        "net_of_fees_ok": bool(nof),
        "reports": reports,
        "debate": {"bull": (bull or {}).get("argument", ""),
                   "bear": (bear or {}).get("argument", ""),
                   "plan": {"rating": plan.get("rating"), "rationale": plan.get("rationale")}},
        "trader": {"action": trader.get("action"), "reasoning": trader.get("reasoning")},
        "risk": {"aggressive": risk_debate["aggressive"].get("argument", ""),
                 "neutral": risk_debate["neutral"].get("argument", ""),
                 "conservative": risk_debate["conservative"].get("argument", ""),
                 "verdict": verdict.get("thesis", "")},
    }


def run_symbol(symbol):
    """Exécute le pipeline complet pour un symbole. Renvoie FirmDecision (dict) ou None
    (fail-safe : si <2 analystes répondent, pas de décision plutôt qu'une décision fictive)."""
    symbol = symbol.upper()
    snap = _snap(symbol)
    state = _state(symbol)
    if not snap and not state:
        return None
    # 1) ANALYSTES (local) — chacun ses blocs internes pertinents
    reports = {
        "technical": _analyst("technique", "Choisis un sous-ensemble non-redondant "
                              "(tendance/momentum/volatilité/volume) ; multi-timeframe.",
                              {"prix": snap, "market": state.get("market"),
                               "orderflow": state.get("orderflow"), "consensus_banc": state.get("brain")}),
        "sentiment": _analyst("sentiment", "Fear&Greed, funding, long/short, OI, taker ; "
                             "contrarien AUX EXTRÊMES seulement.",
                             {"sentiment": state.get("sentiment"), "carry": state.get("carry"),
                              "liquidations": state.get("liquidations"), "orderflow": state.get("orderflow")}),
        "news": _analyst("news/macro", "Catalyseurs + macro (CPI->taux->DXY->BTC) ; "
                        "distingue déjà price-in.",
                        {"macro": state.get("macro"), "rdv": state.get("rdv"),
                         "bitget_watch": state.get("bitget_watch")}),
        "fundamental": _analyst("fondamental", "On-chain (MVRV-Z/NVT/flux), tokenomics, "
                               "DeFi ; horizon LENT.",
                               {"onchain": state.get("onchain"), "flows": state.get("flows"),
                                "market": state.get("market")}),
    }
    if sum(1 for r in reports.values() if r) < 2:
        return None                                # trop d'analystes muets -> pas de décision
    # 2) DÉBAT bull<->bear (local)
    rounds = max(1, int(float(_knob("FIRM_DEBATE_ROUNDS", 1))))
    bull = bear = None
    last_bull = last_bear = ""
    for _ in range(rounds):
        bull = _researcher("bull", reports, last_bear)
        last_bull = bull.get("argument", "")
        bear = _researcher("bear", reports, last_bull)
        last_bear = bear.get("argument", "")
    # 3) research-manager (cloud juge)
    plan = _manager(reports, bull, bear)
    # 4) trader (cloud juge)
    trader = _trader(plan, reports)
    # 5) DÉBAT risque agressif->conservateur->neutre (local, gaté §105 — défaut OFF)
    risk_debate = _risk_round(trader, reports)
    # 6) risk-judge (cloud juge) -> décision finale
    verdict = _risk_judge(plan, trader, risk_debate)
    return _assemble(symbol, snap, reports, bull, bear, plan, trader, risk_debate, verdict)


# ---------------------------------------------------------------- ombre + cache + méta
def _journalise_ombre(decision):
    """§89 — OMBRE firm_shadow : direction×conviction au journal overlay (jugé net-de-frais
    par live_ic_audit, comme qml_shadow/nn_shadow). Best-effort, jamais bloquant."""
    try:
        px = decision.get("price")
        v = float(decision.get("direction") or 0.0) * float(decision.get("conviction") or 0.0)
        if not px or abs(v) < 1e-9:
            return
        import journal_append as ja
        ja.append_jsonl(OVERLAY, {"ts": int(time.time()), "symbol": decision["symbol"],
                                  "price": float(px), "votes": {"firm_shadow": round(v, 3)}})
    except Exception:
        pass


def _write_cache(decisions):
    """Cache par symbole (dashboard + 19ᵉ voix). + méta pour voice_shadow_measure."""
    try:
        DECISIONS.write_text(json.dumps({"updated": int(time.time()),
                                         "by_symbol": decisions}, default=str), encoding="utf-8")
    except Exception:
        pass
    try:                                           # wf_edge n/a (LLM non entraîné) -> gate fermé
        META.write_text(json.dumps({"meta": {"wf_edge": None, "updated": int(time.time()),
                                              "n_symbols": len(decisions)}}), encoding="utf-8")
    except Exception:
        pass


def cycle():
    """Exécute la firme sur tout l'univers. No-op si OFF / kill-switch. Journalise l'ombre
    et écrit le cache. Retourne le nombre de décisions émises."""
    _load_env()                                    # cron nu : garantir que .env est vu avant os.getenv
    if not enabled() or _kill_switched():
        return 0
    try:
        import universe
        syms = universe.symbols()
    except Exception:
        syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    wl = str(_knob("FIRM_SYMBOLS", "")).strip()
    if wl:
        syms = [s.strip().upper() for s in wl.split(",") if s.strip()]
    decisions = {}
    for sym in syms:
        try:
            d = run_symbol(sym)
        except Exception:                          # fail-safe par symbole
            d = None
        if d:
            decisions[sym] = d
            _journalise_ombre(d)
    if decisions:
        _write_cache(decisions)
    return len(decisions)


def latest(symbol=None):
    """Lecture du cache (aucun appel LLM). dict par symbole, ou une décision si symbol donné."""
    try:
        d = json.loads(DECISIONS.read_text(encoding="utf-8")).get("by_symbol", {})
    except Exception:
        d = {}
    if symbol:
        return d.get(symbol.upper())
    return d


def main():
    _load_env()                                    # cron/CLI nu : charger .env avant tout os.getenv
    args = sys.argv[1:]
    if "--status" in args:
        d = latest()
        print("=== FIRME DE TRADING (dernier cache — CONSULTATION, aucun appel LLM) ===")
        print(f"enabled={enabled()} · kill_switch={_kill_switched()} · symboles={len(d)}")
        for sym, dec in d.items():
            print(f"  {sym:10s} {dec.get('rating'):11s} dir={dec.get('direction'):+.2f} "
                  f"conv={dec.get('conviction'):.2f} net_frais={dec.get('net_of_fees_ok')} "
                  f"taille={dec.get('sizing_suggested_usdt')}$")
        print("Lecture seule, aucun ordre. VERDICT: SAFE")
        return 0
    if "--symbol" in args:
        i = args.index("--symbol")
        sym = args[i + 1] if i + 1 < len(args) else "BTCUSDT"
        if not enabled():
            print("FIRM_ENABLED=OFF — firme désarmée (aucun appel). VERDICT: SAFE")
            return 0
        d = run_symbol(sym)
        if d:
            _journalise_ombre(d)
            _write_cache({**latest(), sym.upper(): d})
        print(json.dumps(d, indent=2, default=str, ensure_ascii=False))
        return 0
    if "--cycle" in args:
        n = cycle()
        print(f"firme: {n} décision(s) émise(s) (enabled={enabled()}). VERDICT: SAFE")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
