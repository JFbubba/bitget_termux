"""
journal_append.py — journaux APPEND-ONLY en JSONL, avec rotation par taille.

Classement : SAFE. Aucun réseau, aucun ordre. Écrit uniquement des fichiers
locaux gitignorés (*.jsonl est dans .gitignore ; safe_push_check interdit de
toute façon leur suivi git).

Pourquoi (audit 03/07, lot P2) : brain_log.json est une FENÊTRE glissante de
500 entrées ≈ 6 h d'historique — la revue J+14 (seuils, edge temporel, PnL)
n'aurait RIEN à lire. Les journaux d'apprentissage et de décision passent par
ici : une ligne JSON par évènement, append-only (pas de réécriture du fichier
entier), rotation en .old au-delà du budget (jamais de croissance non bornée,
jamais de fichier corrompu — une ligne s'écrit ou ne s'écrit pas).
"""

import json
from pathlib import Path


def append_jsonl(path, entry, max_bytes=100_000_000):
    """Ajoute UNE ligne JSON à `path` (append-only, best-effort : ne lève jamais).
    Si le fichier dépasse `max_bytes`, il bascule en `<path>.old` (l'ancien .old
    est remplacé) et un fichier neuf démarre — ~2× le budget au pire sur disque.
    Retourne True si la ligne a été écrite."""
    try:
        p = Path(path)
        if p.exists() and p.stat().st_size >= int(max_bytes):
            old = p.with_suffix(p.suffix + ".old")
            p.replace(old)                        # atomique ; l'ancien .old disparaît
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def read_jsonl(path, limit=None):
    """Lit les lignes JSON de `path` (les illisibles sont ignorées). PUR côté
    parsing. `limit` = ne garder que les N dernières. [] si absent/illisible."""
    out = []
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-int(limit):] if limit else out
