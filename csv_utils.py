"""csv_utils.py — lecture de lignes de journaux CSV + recherche tolérante (lecture seule).

Classement : SAFE. Aucune écriture, aucun réseau, aucun ordre, aucun secret.

`read_csv_rows` et `find_value` étaient dupliqués à l'identique dans les deux
moteurs de pré-ordres (`order_signal_engine`, `preorder_engine`). On les
centralise ici (mêmes contrats, sémantique inchangée pour les appelants).
"""

import csv


def read_csv_rows(path):
    """Lit un CSV en liste de dicts ; renvoie [] si le fichier n'existe pas."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_value(row, candidates):
    """Renvoie la 1re valeur non vide parmi `candidates` (clés insensibles à la
    casse), ou "" si aucune ne correspond."""
    lower_map = {k.lower(): v for k, v in row.items()}
    for candidate in candidates:
        value = lower_map.get(candidate.lower())
        if value not in [None, ""]:
            return value
    return ""
