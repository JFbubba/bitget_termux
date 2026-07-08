"""verrous_effectifs.py — état EFFECTIF des verrous d'exécution + leur SOURCE.

SAFE : LECTURE SEULE, aucun ordre. Charge .env comme le bot puis évalue chaque
verrou avec la VRAIE logique `.env OR config` (miroir de
`futures_executor._futures_autonomous_live` : env_on OR cfg). Expose summary()
pour le dashboard + un CLI de diagnostic.

Motivation : l'état armé/paper est éparpillé ET trompeur — `config.py` peut afficher
`False` alors que `.env` arme le réel via le OR. Cette vue CONSOLIDE l'effectif ET
la source, et signale les ÉCARTS, pour qu'on ne s'y reprenne plus (ni humain, ni agent).
"""
from __future__ import annotations
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:                                        # charger .env comme le bot (runtime)
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except Exception:
    pass

from config_utils import cfg  # noqa: E402  (source config.py)

TRUEISH = ("1", "true", "yes", "on")


def _flag(name, config_default=False):
    """État d'un verrou et sa source, selon la logique du bot : .env OU config."""
    env_on = (os.getenv(name) or "").strip().lower() in TRUEISH
    cfg_on = bool(cfg(name, config_default))
    eff = env_on or cfg_on
    src = ".env" if (env_on and not cfg_on) else \
          "config" if (cfg_on and not env_on) else \
          ".env+config" if eff else "—"
    return {"effectif": eff, "source": src, "env": env_on, "config": cfg_on,
            "ecart": env_on != cfg_on}


def summary():
    """Vue consolidée de l'armement réel. Dict pur (best-effort, sans réseau)."""
    try:
        import mandate
        mandate_live = bool(mandate.live_enabled())
    except Exception:
        mandate_live = bool(cfg("MANDATE_LIVE_ENABLED", False))
    fut = _flag("FUTURES_AUTONOMOUS_LIVE")
    acc = _flag("ACCUM_AUTONOMOUS_LIVE")
    edge = int(cfg("FUTURES_EDGE_GATE_OVERRIDE", 0) or 0)
    kill = (HERE / "KILL_SWITCH").exists()
    surfaces = {k: _flag(k)["effectif"] for k in
                ("SPOT_TRADE_LIVE", "MARGIN_TRADE_LIVE", "TRANSFER_LIVE", "EARN_LIVE")}
    n_surf = sum(surfaces.values())

    futures_actif = mandate_live and fut["effectif"] and not kill
    accum_actif = mandate_live and acc["effectif"] and not kill

    if kill:
        resume = "KILL_SWITCH ACTIF — tout bloqué"
    elif not mandate_live:
        resume = "PAPER (verrou maître coupé)"
    elif futures_actif or accum_actif:
        parts = (["futures"] if futures_actif else []) + (["accum"] if accum_actif else [])
        if n_surf:
            parts.append(f"{n_surf}/4 surfaces")
        resume = "RÉEL armé : " + ", ".join(parts)
    else:
        resume = "PAPER (aucun 2e verrou armé)"

    ecarts = [k for k, v in {"FUTURES_AUTONOMOUS_LIVE": fut,
                             "ACCUM_AUTONOMOUS_LIVE": acc}.items() if v["ecart"]]
    return {
        "resume": resume,
        "mandate_live": mandate_live,
        "futures": {**fut, "actif": futures_actif},
        "accum": {**acc, "actif": accum_actif},
        "edge_gate_override": edge,
        "kill_switch": kill,
        "surfaces": surfaces, "surfaces_armees": n_surf,
        "notional_futures": os.getenv("FUTURES_AUTO_NOTIONAL_USDT")
        or cfg("FUTURES_AUTO_NOTIONAL_USDT", 10),
        "ecarts": ecarts,   # verrous où .env et config divergent (armés via .env seul)
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=1, ensure_ascii=False))
