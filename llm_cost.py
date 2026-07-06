"""llm_cost.py — budget & ledger de coût de l'agent LLM (idée NERVA cost_control).

Classement : SAFE (écrit un ledger JSONL local, aucun ordre, aucun secret). Borne et
AUDITE la dépense des appels LLM CLOUD (Gemini / OpenRouter). Le backend LOCAL (Ollama)
est gratuit -> non compté.

Deux plafonds JOURNALIERS, les DEUX doivent tenir (budget_ok) :
  • coût $ cumulé du jour < LLM_AGENT_DAILY_BUDGET_USD ;
  • nombre d'appels du jour < LLM_AGENT_DAILY_MAX_CALLS (borne les modèles « gratuits »
    type Gemini free-tier dont le coût $ est ~0 mais le quota de requêtes est limité).
Dépassé -> l'agent LLM n'appelle plus le cloud du jour (fail-safe -> vote neutre ignoré).
Ledger illisible -> today() renvoie (0,0) : on n'empêche pas à tort (le débit reste borné
par le throttle TTL par symbole de l'agent).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from config_utils import cfg as _cfg

LEDGER = Path(__file__).resolve().parent / ".llm_cost_ledger.jsonl"


def _day(ts=None):
    return int((ts if ts is not None else time.time()) // 86400)


def record(backend, model, tokens=0, cost_usd=0.0, now=None):
    """Journalise un appel LLM cloud (append-only, best-effort — ne lève jamais)."""
    now = time.time() if now is None else now
    row = {"ts": round(now, 1), "day": _day(now), "backend": str(backend),
           "model": str(model), "tokens": int(tokens or 0),
           "cost_usd": round(float(cost_usd or 0), 6)}
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load(ledger=None):
    if ledger is not None:
        return ledger
    rows = []
    try:
        if LEDGER.exists():
            for line in LEDGER.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def today(now=None, ledger=None):
    """(coût $, nb d'appels) du JOUR courant. (0.0, 0) si ledger illisible/vide."""
    day = _day(now)
    rows = [r for r in _load(ledger) if isinstance(r, dict) and r.get("day") == day]
    cost = sum(float(r.get("cost_usd", 0) or 0) for r in rows)
    return round(cost, 6), len(rows)


def budget_ok(now=None, ledger=None):
    """True si le JOUR courant est sous les DEUX plafonds (coût $ ET nb d'appels)."""
    cost, n = today(now=now, ledger=ledger)
    return (cost < float(_cfg("LLM_AGENT_DAILY_BUDGET_USD", 0.50))
            and n < int(_cfg("LLM_AGENT_DAILY_MAX_CALLS", 2000)))
