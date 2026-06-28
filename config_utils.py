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


def cfg(name, fallback):
    """Valeur de config.<name>, ou `fallback` si config indisponible. PUR (best-effort)."""
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback
