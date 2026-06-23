"""
runtime_cache.py — cache TTL + dégradation gracieuse (« stale-while-error »).

Classement : SAFE. Ce module ne fait AUCUN appel réseau propre : il ne fait
qu'envelopper des fonctions `fetch` fournies par l'appelant, en mémorisant leur
résultat. La logique TTL/fraîcheur est **pure et testable** (horloge injectable).

POURQUOI (réponse à « optimiser la dépendance externe au runtime ») :
  Le cerveau lit ~7 sources réseau par décision (orderflow, macro, sentiment,
  derivs, liquidations…). Sans cache, chaque lecture = autant d'appels synchrones,
  chacun une source de latence et de panne ; le dashboard qui *poll* en rajoute.
  Ici :
    • dans le TTL            -> servi depuis la mémoire/disque, AUCUN appel réseau ;
    • échec de rafraîchissement -> on sert la dernière valeur connue (« stale ») ;
    • aucune valeur connue   -> fallback neutre.
  Conséquence : le cerveau ne **bloque jamais** sur une source morte, et la
  latence de décision est découplée de la latence réseau (cf. RESEARCH_NOTES §1,
  « latency = alpha »).
"""

import json
import time
from pathlib import Path

CACHE_FILE = Path(__file__).resolve().parent / ".runtime_cache.json"
_MEM = {}


def _now():
    return time.time()


def _load_disk():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_disk(d):
    try:
        CACHE_FILE.write_text(json.dumps(d)[:2_000_000], encoding="utf-8")
    except Exception:
        pass


def decide(entry, ttl, now):
    """PUR : à partir d'une entrée {ts, val} (ou None), décide l'état du cache.

    Retourne ('fresh'|'stale'|'miss', value). 'fresh' = dans le TTL (réutiliser),
    'stale' = expiré mais valeur connue (à rafraîchir, repli possible), 'miss' =
    rien en cache."""
    if not entry:
        return ("miss", None)
    age = now - entry.get("ts", 0)
    if age < ttl:
        return ("fresh", entry.get("val"))
    return ("stale", entry.get("val"))


def get(key, ttl, fetch, fallback=None, now=None):
    """Renvoie une valeur fraîche si possible, sinon stale, sinon fallback.

    `fetch` n'est appelée que si l'entrée est expirée ou absente. Toute exception
    de `fetch` est absorbée : on dégrade vers la dernière valeur connue."""
    now = _now() if now is None else now
    entry = _MEM.get(key)
    if entry is None:
        entry = _load_disk().get(key)
    state, val = decide(entry, ttl, now)
    if state == "fresh":
        return val
    try:
        fresh = fetch()
    except Exception:
        return val if state == "stale" else fallback   # stale-while-error
    rec = {"ts": now, "val": fresh}
    _MEM[key] = rec
    disk = _load_disk()
    disk[key] = rec
    _save_disk(disk)
    return fresh


def stats():
    """État du cache (diagnostic) : nb d'entrées et âge par clé."""
    now = _now()
    keys = set(_MEM) | set(_load_disk())
    out = {}
    for k in keys:
        e = _MEM.get(k) or _load_disk().get(k)
        if e:
            out[k] = round(now - e.get("ts", now), 1)
    return {"entries": len(out), "age_s": out}
