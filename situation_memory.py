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


def _pearson(xs, ys):
    """PUR, sans dépendance. Corrélation de Pearson entre deux listes. 0.0 si dégénéré.
    On l'utilise plutôt que hit-rate-vs-base parce qu'elle est RÉGIME-NEUTRE : le
    hit-rate est confondu par le biais directionnel de la fenêtre (un marché qui tend
    -> base_rate haute -> suivre la tendance « gagne » gratuitement, §97), la corrélation
    retire ce biais constant et mesure la vraie information."""
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    d = (dx * dy) ** 0.5
    return num / d if d > 0 else 0.0


def evaluate(store=None, path=None, max_eval=1200, min_warm=300, min_samples=3):
    """LE « read » qui manquait (§97). Mesure walk-forward : la mémoire PRÉDIT-elle ?
    Pour chaque situation de la fenêtre récente, `expectancy_hint` est calculé sur le
    PASSÉ SEUL (store=rows[:i]) et confronté au résultat réalisé. Sans cette mesure, on
    écrivait 17k lignes sans jamais savoir si elles servaient — elles ne servaient pas
    (IC hint↔résultat −0.01, t −1.3 sur 16k au 07/07). VERDICT sur l'IC (régime-neutre),
    PAS sur hit-rate-vs-base (confondu par le régime, flippe de signe selon la fenêtre).
    Retourne {n, ic, ic_t, hit_rate, base_rate, edge_vs_base} ou {n:<30}. Fenêtre bornée
    (coût stable quand le journal grossit). PUR si store injecté."""
    import math
    rows = [r for r in _load(store, path)
            if isinstance(r, dict) and r.get("tokens") and r.get("outcome") is not None]
    rows.sort(key=lambda r: r.get("ts", 0))
    if len(rows) > 5000:                  # borne le coût (prédictivité RÉCENTE), stable en croissance
        rows = rows[-5000:]
    if len(rows) < int(min_warm) + 30:
        return {"n": 0}
    debut = max(int(min_warm), len(rows) - int(max_eval))
    preds, outs, hits = [], [], 0
    for i in range(debut, len(rows)):
        situ = dict(t.split("=", 1) for t in rows[i]["tokens"] if "=" in t)
        h = expectancy_hint(situ, min_samples=min_samples, store=rows[:i])
        if h is None:
            continue
        hint, real = h["hint"], rows[i]["outcome"]
        if hint == 0 or real == 0:
            continue
        preds.append(hint)
        outs.append(real)
        hits += 1 if (hint > 0) == (real > 0) else 0
    n = len(preds)
    if n < 30:
        return {"n": n}
    base = sum(1 for o in outs if o > 0) / n
    ic = _pearson(preds, outs)
    ic_t = ic * math.sqrt((n - 2) / max(1e-9, 1.0 - ic * ic))   # eps : t grand mais fini si ic≈1
    return {"n": n, "ic": round(ic, 4), "ic_t": round(ic_t, 2),
            "hit_rate": round(hits / n, 3), "base_rate": round(max(base, 1.0 - base), 3),
            "edge_vs_base": round(hits / n - max(base, 1.0 - base), 3)}
