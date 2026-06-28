"""
market_timing.py — évaluation TEMPORELLE des agents MARCHÉ-LARGE (macro, sentiment).

Classement : SAFE. Lecture seule / advisory, AUCUN ordre, AUCUNE clé.

Pourquoi (RESEARCH_NOTES §39) : macro et sentiment sont des signaux MARCHÉ-LARGE (le vote
ignore le symbole / Fear&Greed est global). L'étalon transversal (rank IC cross-sectionnel)
les zéro-note PAR CONSTRUCTION — on ne peut pas mesurer un signal market-wide en classant des
symboles. Leur edge éventuel est TEMPOREL : le vote à l'instant t prédit-il le rendement FUTUR
du MARCHÉ (proxy BTC) ? Ce module accumule un historique QUOTIDIEN (vote macro/sentiment + prix
marché) et mesure l'IC temporelle. Verdict DANS LE TEMPS (semaines/mois : macro/F&G bougent
lentement) — comme l'accumulation microstructure. Ne promeut RIEN ; toute promotion = déflation
+ OOS + GO explicite.
"""

import json
import time
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent / "market_timing_history.jsonl"
_LAST_LOG = {}


def snapshot(now=None):
    """Relevé courant : votes macro & sentiment (marché-large) + prix marché (BTC). Best-effort.
    None si indisponible (jamais d'exception)."""
    now = time.time() if now is None else now
    rec = {"ts": int(now)}
    try:
        import swarm_brain as sb
        rec["macro"] = float((sb.agent_macro("BTCUSDT") or {}).get("vote", 0.0) or 0.0)
        rec["sentiment"] = float((sb.agent_sentiment("BTCUSDT") or {}).get("vote", 0.0) or 0.0)
    except Exception:
        return None
    try:
        import market_sources as ms
        cl = ms.closes("BTCUSDT", limit=5)
        rec["market"] = float(cl[-1]) if cl else None
    except Exception:
        rec["market"] = None
    return rec if rec.get("market") else None


def log_daily(now=None, every_s=72000):
    """Append-only QUOTIDIEN (throttle ~20 h) du relevé dans HISTORY_FILE. Best-effort, ne lève
    jamais. Accumule le jeu évaluable au fil des jours. Retourne 1 si écrit, 0 sinon."""
    now = time.time() if now is None else now
    if now - float(_LAST_LOG.get("ts", 0.0)) < float(every_s):
        return 0
    rec = snapshot(now)
    if not rec:
        return 0
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _LAST_LOG["ts"] = now
        return 1
    except Exception:
        return 0


def load_history(path=None):
    p = Path(path) if path else HISTORY_FILE
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return out


def evaluate(rows, horizon=5, agent="macro"):
    """IC TEMPORELLE : vote_t de l'agent marché-large vs rendement FUTUR du marché sur `horizon`
    enregistrements (jours). PUR. rank IC + t-stat via l'étalon agent_validation. Pas de verdict
    tant que n est petit (accumulation ; macro/F&G bougent lentement)."""
    rows = sorted([r for r in rows if r.get("market")], key=lambda r: r.get("ts", 0))
    votes, fwd = [], []
    for i in range(len(rows) - int(horizon)):
        m0, m1 = rows[i].get("market"), rows[i + int(horizon)].get("market")
        v = rows[i].get(agent)
        if m0 and m1 and v is not None:
            votes.append(float(v)); fwd.append(float(m1) / float(m0) - 1.0)
    if len(votes) < 10:
        return {"agent": agent, "n": len(votes), "ic": 0.0, "ic_t": 0.0,
                "note": "accumulation en cours (données insuffisantes)"}
    try:
        import agent_validation as av
        ic = av.rank_ic(votes, fwd)
        return {"agent": agent, "n": len(votes), "ic": round(ic, 4),
                "ic_t": round(av.ic_tstat(ic, len(votes)), 2), "horizon_days": int(horizon)}
    except Exception:
        return {"agent": agent, "n": len(votes), "ic": 0.0, "ic_t": 0.0, "note": "étalon indisponible"}


def report(horizon=5, path=None):
    """Résumé d'accumulation + edge temporel (macro & sentiment). Lecture seule."""
    rows = load_history(path)
    span = round((rows[-1]["ts"] - rows[0]["ts"]) / 86400.0, 1) if len(rows) >= 2 else 0.0
    return {"n_records": len(rows), "span_days": span,
            "edge": {a: evaluate(rows, horizon, a) for a in ("macro", "sentiment")}}
