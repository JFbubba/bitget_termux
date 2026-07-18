"""config_utils.py — lecture de la config avec repli robuste (lecture seule).

Classement : SAFE. Aucune écriture, aucun réseau, aucun ordre, aucun secret.

`_cfg(name, fallback)` était dupliqué à l'identique dans 11 modules (risk_manager,
mandate, spot_executor, futures_executor, edge_ladder, risk_limits,
accumulation_engine, universe, bitget_hub_bridge, equity_curve, macro_regime).
Source unique ici. Lit l'attribut `name` du module `config` (la SOURCE UNIQUE des
défauts, audit #4) et retombe sur `fallback` si config est absent/illisible.

Les modules l'importent via `from config_utils import cfg as _cfg` : le nom local
`_cfg` (et la référence `module._cfg` utilisée par les tests) restent inchangés.
"""


import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def cfg(name, fallback):
    """Valeur de config.<name>, ou `fallback` si config indisponible. PUR (best-effort).

    ⚠️ config.py SEUL — AVEUGLE à os.environ/.env. À réserver aux DÉFAUTS et aux knobs
    volontairement config-only (murs constitutionnels). Pour un réglage surchargable par
    `.env` (verrous, edge gate, caps effectifs), utiliser env_flag/env_str/env_num."""
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


def load_env(path=None, override=False):
    """CHARGEUR CANONIQUE de `.env` dans os.environ (best-effort, idempotent). N'ÉCRASE PAS
    l'existant sauf override=True. Remplace les ~25 load_dotenv() épars + les _load_env()
    maison (news_agent/learning_health). Appelé une fois en tête de config.py -> tout process
    important `config` (donc quasi tous) voit `.env`, y compris un python nu (cron/diagnostic).
    Sans effet si `.env` absent. python-dotenv si dispo, sinon parseur manuel."""
    p = Path(path) if path else _ROOT / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(p), override=override)
        return
    except Exception:
        pass
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k and (override or k not in os.environ):
                os.environ[k] = v.strip()
    except Exception:
        pass


def env_str(name, fallback):
    """`.env`/os.environ > config.<name> > fallback. Valeur env vide ('' ou espaces) ignorée."""
    v = os.getenv(name)
    if v is not None and v.strip() != "":
        return v.strip()
    return cfg(name, fallback)


def env_flag(name, fallback=False):
    """Booléen env-first à parsing STRICT : 1/true/yes/on -> True, 0/false/no/off -> False.
    ⚠️ '0' -> False (là où bool(os.getenv('X')) serait True à tort — DANGER pour les murs).
    Valeur env non reconnue -> ignorée (repli config). Sinon bool(config.<name>) ou fallback."""
    v = os.getenv(name)
    if v is not None:
        s = v.strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
    return bool(cfg(name, fallback))


def env_num(name, fallback):
    """Nombre (float) env-first. Env absent/illisible -> config.<name> -> fallback."""
    v = os.getenv(name)
    if v is not None and v.strip() != "":
        try:
            return float(v.strip())
        except ValueError:
            pass
    try:
        return float(cfg(name, fallback))
    except (TypeError, ValueError):
        return fallback
