"""situation_memory.py — mémoire de situations + réflexion post-trade (idée 111/TradingAgents).

Classement : SAFE (lit/écrit un JSONL local, aucun ordre, aucun secret, aucun réseau).
Méta-apprentissage OFFLINE sans ré-entraînement : on stocke (situation de marché -> résultat
réalisé), et on RETROUVE les situations passées les plus proches pour éclairer la décision
courante (« déjà vu ce profil consensus/régime -> voilà ce qui a marché »). Complète
l'apprentissage EARCP (qui pondère les AGENTS, pas les SITUATIONS).

Similarité SANS dépendance : Jaccard sur des features DISCRÉTISÉES (tokens « clé=valeur »).
ADVISORY seulement — hors chemin critique, ne déclenche jamais un ordre.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

MEMORY = Path(__file__).resolve().parent / ".situation_memory.jsonl"


def tokens(situation):
    """PUR. Situation {clé: valeur} -> ensemble de tokens 'clé=valeur' (valeurs
    discrétisées attendues : str ou bucket). Les floats sont arrondis grossièrement."""
    out = set()
    for k, v in (situation or {}).items():
        if isinstance(v, float):
            v = round(v, 2)
        out.add(f"{k}={v}")
    return out


def similarity(a, b):
    """PUR. Jaccard entre deux ensembles de tokens : |a∩b| / |a∪b| (0..1)."""
    a, b = set(a), set(b)
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def record(situation, outcome, now=None, path=None):
    """Journalise (situation -> résultat) en append-only (best-effort, ne lève jamais).
    `outcome` : nombre (+1 correct / -1 raté, ou un PnL). C'est la RÉFLEXION post-trade."""
    now = time.time() if now is None else now
    row = {"ts": round(now, 1), "tokens": sorted(tokens(situation)),
           "outcome": float(outcome)}
    try:
        with open(path or MEMORY, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load(store=None, path=None):
    if store is not None:
        return store
    rows = []
    try:
        p = path or MEMORY
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def recall(situation, n=5, min_sim=0.34, store=None, path=None):
    """Les n situations passées les plus PROCHES (sim >= min_sim), triées décroissant.
    Retourne [{sim, outcome, tokens}]. [] si mémoire vide/illisible."""
    cur = tokens(situation)
    scored = []
    for r in _load(store, path):
        if not isinstance(r, dict):
            continue
        s = similarity(cur, r.get("tokens") or [])
        if s >= min_sim:
            scored.append({"sim": round(s, 3), "outcome": float(r.get("outcome", 0) or 0),
                           "tokens": r.get("tokens")})
    scored.sort(key=lambda x: -x["sim"])
    return scored[:int(n)]


def expectancy_hint(situation, min_samples=3, store=None, path=None):
    """Espérance ADVISORY des situations similaires : moyenne des résultats passés pondérée
    par la similarité. Retourne {n, hint} ou None si trop peu d'échantillons (prudence)."""
    sims = recall(situation, n=50, store=store, path=path)
    if len(sims) < int(min_samples):
        return None
    wsum = sum(x["sim"] for x in sims) or 1.0
    hint = sum(x["sim"] * x["outcome"] for x in sims) / wsum
    return {"n": len(sims), "hint": round(hint, 3)}
