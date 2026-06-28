"""numeric_utils.py — utilitaires numériques purs et partagés (lecture seule).

Classement : SAFE. Aucune I/O, aucun réseau, aucun ordre, aucun secret.

`safe_float` était dupliqué dans une dizaine de modules (rapports / outcome /
pré-ordres) avec des variantes divergentes. On centralise ici une version unique
et robuste :

  - renvoie `default` pour None / chaîne vide ;
  - capture `(ValueError, TypeError)` — donc un type inattendu rend `default`
    au lieu de planter (plus robuste que les ex-variantes `except ValueError`) ;
  - `decimal_comma=True` tolère la virgule décimale ("3,14" -> 3.14) pour les
    modules qui lisent des journaux potentiellement localisés (ex-variante E).

Les modules qui dépendaient d'un défaut `0.0` (rapports) ou de la virgule
(pré-ordres) conservent leur contrat via un fin wrapper local qui fixe ces
options — le comportement observable reste identique pour leurs appelants.
"""


def safe_float(value, default=None, *, decimal_comma=False):
    """Convertit `value` en float ; renvoie `default` si vide/None/invalide.

    decimal_comma=True : tolère la virgule décimale ("3,14" -> 3.14)."""
    try:
        if value is None or value == "":
            return default
        if decimal_comma:
            value = str(value).replace(",", ".")
        return float(value)
    except (ValueError, TypeError):
        return default
