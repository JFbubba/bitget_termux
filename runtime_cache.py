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
import os
import threading
import time
from pathlib import Path

CACHE_FILE = Path(__file__).resolve().parent / ".runtime_cache.json"
_MEM = {}
_LOCK = threading.Lock()          # sérialise le read-modify-write disque INTRA-process
MAX_DISK_BYTES = 2_000_000        # budget disque du cache (éviction PAR CLÉ au-delà)


def _now():
    return time.time()


def _load_disk():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_disk(d):
    """Écriture ATOMIQUE (tmp + os.replace) avec ÉVICTION PAR CLÉ au-delà du budget.
    L'ancienne troncature par slicing json.dumps(d)[:2Mo] produisait, au seuil, un
    JSON INVALIDE -> perte TOTALE et silencieuse du cache au rechargement (audit
    03/07). Ici : on retire les plus GROSSES valeurs jusqu'à rentrer dans le budget
    (dégradation par clé, jamais de fichier corrompu), et le remplacement atomique
    protège les lecteurs concurrents d'un fichier à moitié écrit."""
    try:
        data = json.dumps(d)
        if len(data) > MAX_DISK_BYTES:
            par_taille = sorted(d, key=lambda k: len(json.dumps(d.get(k))), reverse=True)
            for k in par_taille:
                d.pop(k, None)
                data = json.dumps(d)
                if len(data) <= MAX_DISK_BYTES:
                    break
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, CACHE_FILE)
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
    with _LOCK:                    # gather_votes parallélisé : écrivains concurrents
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
