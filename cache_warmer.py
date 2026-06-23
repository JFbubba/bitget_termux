"""
cache_warmer.py — pré-chauffe le runtime_cache (lectures live 100 % locales).

Classement : SAFE (lecture seule, aucun ordre). En appelant les agents une fois,
on remplit `runtime_cache` ; les lectures suivantes du cerveau (et le polling du
dashboard) servent alors depuis le cache au lieu de refrapper les API externes.
À lancer périodiquement (cron / boucle légère) pour que la latence de décision
reste découplée de la latence réseau (cf. RESEARCH_NOTES §1 & §7).

Usage :  python cache_warmer.py BTCUSDT ETHUSDT
"""

import json
import sys

import runtime_cache as rc


def warm(symbols=("BTCUSDT",)):
    """Déclenche un fetch de toutes les sources pour `symbols` -> peuple le cache."""
    import swarm_brain as sb
    warmed, failed = [], []
    for s in symbols:
        s = s.upper()
        try:
            sb.gather_votes(s)      # chaque agent passe par runtime_cache
            sb._series(s)           # série CVIX (Bitget -> CoinGecko, cachée)
            warmed.append(s)
        except Exception as exc:
            failed.append({"symbol": s, "err": type(exc).__name__})
    return {"warmed": warmed, "failed": failed, "cache": rc.stats()}


def main():
    symbols = tuple(a.upper() for a in sys.argv[1:]) or ("BTCUSDT",)
    print(json.dumps(warm(symbols), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
