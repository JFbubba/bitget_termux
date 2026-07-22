"""Fixtures partagées de la suite pytest (COMPLÉMENTAIRE de tests_audit.py — qui
reste la porte officielle des 3 portes ; cette suite est un banc unitaire de dev).

Lancement :  pytest          (depuis la racine ; pytest.ini borne la collecte à tests/)
Dépendance : pytest (requirements-optional.txt) — le bot tourne SANS.

Règles : les tests n'écrivent RIEN (journaux injectés, cf. ERR-019) et n'appellent
jamais le réseau — modules PURS uniquement, paramètres injectés.
"""
import sys
from pathlib import Path

import pytest

REPO = str(Path(__file__).resolve().parent.parent)
if REPO not in sys.path:
    sys.path.insert(0, REPO)


@pytest.fixture
def env_kelly(monkeypatch):
    """Épingle les knobs env de kelly.py à des valeurs connues.

    Nécessaire car `kelly.py` exécute `_load_env()` à l'import : le `.env` du VPS
    définit KELLY_FRACTION / KELLY_MAX_FRACTION, donc les tests qui passent par
    `_knob` sans injection seraient non déterministes. monkeypatch restaure tout
    après chaque test (isolation).
    """
    def _set(fraction="0.5", max_fraction="0.25", prior_strength="100"):
        monkeypatch.setenv("KELLY_FRACTION", fraction)
        monkeypatch.setenv("KELLY_MAX_FRACTION", max_fraction)
        monkeypatch.setenv("KELLY_PRIOR_STRENGTH", prior_strength)
    return _set
