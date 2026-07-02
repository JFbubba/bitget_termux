"""
brain_validation.py — validation T5 PLANIFIÉE (auto-throttlée) des agents.

Classement : SAFE. Lecture seule + écrit un rapport JSON. AUCUN ordre, ne modifie PAS
les poids du cerveau (advisory — l'utilisateur décide de promouvoir).

Pourquoi (audit #9) : agent_validation (Rank IC / PSR / DSR / haircut) ne tournait sur
aucun scheduler. Ce script l'exécute AU PLUS une fois toutes ~`MIN_INTERVAL_H` heures
(coûteux : replay des agents sur l'historique), écrit `validation_report.json` daté,
et propose des poids a priori (advisory). On ne laisse PAS un poids dériver de 1.0
sans qu'un agent batte le seuil déflaté — mais l'application reste manuelle.
"""

import json
import time
from pathlib import Path

REPORT_FILE = Path(__file__).resolve().parent / "validation_report.json"
# Légèrement SOUS la période du timer dédié (bitget-validation.timer, 6h) : un timer
# qui tire pile à 6h ne doit pas être sauté par son propre throttle (ceinture-bretelles
# si quelqu'un relance le script à la main entre deux tirs).
MIN_INTERVAL_H = 5.5


def _stale(now=None):
    """Le dernier rapport est-il assez vieux pour relancer ? (auto-throttle)."""
    try:
        age_h = ((time.time() if now is None else now) - REPORT_FILE.stat().st_mtime) / 3600.0
        return age_h >= MIN_INTERVAL_H
    except Exception:
        return True                                  # pas de rapport -> lancer


def build_output(symbol, ranked, live, timing=None, now=None, mode="mono"):
    """Assemble le rapport de validation (PUR, testable). 'ranked' = ranking replay,
    de PRÉFÉRENCE la coupe TRANSVERSALE (mode="xs", rank_pure_agents_xs : n EFFECTIF
    corrigé de la corrélation transversale — RESEARCH_NOTES §40 : sur un seul symbole
    n plafonne à ~64 < MANDATE_FUTURES_MIN_SAMPLES=120, le palier LIVE était
    mathématiquement inatteignable ; la breadth honnête le rend ATTEIGNABLE sans
    baisser aucun seuil). Repli mono-symbole (mode="mono") si l'univers est
    indisponible. 'live' = edge mesure sur les VOTES REELS journalises (brain_log,
    chemin 2) — ADDITIF / informatif : ne change PAS a lui seul la decision de palier
    (qui lit 'ranking', le replay). Sert a comparer edge backtest
    vs edge live et a preparer une porte plus honnete (replay ET live).
    'timing' = edge TEMPOREL market-timing (chemin 3, RESEARCH_NOTES §39) : la coupe
    transversale zero-note PAR CONSTRUCTION les agents marche-large (macro, sentiment,
    flows) ; cette section mesure si leur vote moyen predit le rendement du MARCHE dans
    le temps. Time-gated (s'accumule avec les semaines de votes), ADVISORY."""
    import agent_validation as av
    return {
        "generated_at": int(time.time() if now is None else now),
        "symbol": symbol,
        "ranking_mode": mode,
        "n_symbols": int(ranked.get("n_symbols", 1) or 1),
        "ranking": ranked.get("agents", []),
        "deflation": ranked.get("deflation", {}),
        "weight_priors_advisory": av.suggest_weight_priors(ranked),
        "live": {"agents": (live or {}).get("agents", []),
                 "n_entries": (live or {}).get("n_entries", 0)},
        "market_timing": {"agents": (timing or {}).get("agents", []),
                          "n_cycles": (timing or {}).get("n_cycles", 0),
                          "n_echantillons": (timing or {}).get("n_echantillons", 0),
                          "horizon_cycles": (timing or {}).get("horizon_cycles", 0)},
    }


def main():
    if not _stale():
        print(f"brain_validation : rapport récent (< {MIN_INTERVAL_H}h), saute. VERDICT: SAFE")
        return
    try:
        import config
        symbol = config.SYMBOLS[0] if getattr(config, "SYMBOLS", None) else "BTCUSDT"
    except Exception:
        symbol = "BTCUSDT"
    try:
        import agent_validation as av
        # coupe TRANSVERSALE d'abord (n EFFECTIF, breadth honnête, §40) ; repli mono.
        mode = "xs"
        try:
            ranked = av.run_xs()
        except Exception:
            ranked = {"error": "run_xs indisponible"}
        if ranked.get("error"):
            mode = "mono"
            ranked = av.run(symbol)
        if ranked.get("error"):
            print(f"brain_validation indisponible : {ranked['error']}")
            return
        live, timing = {}, {}
        try:
            import swarm_brain
            log = swarm_brain._read_log()
            live = av.evaluate_from_log(log)                       # chemin 2 : votes reels
            timing = av.evaluate_market_timing(log)                # chemin 3 : market-timing (§39)
        except Exception:
            pass
        out = build_output(symbol, ranked, live, timing, mode=mode)
        REPORT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        passed = [a["agent"] for a in ranked.get("agents", []) if a.get("dsr", 0) >= 0.9]
        live_n = out["live"]["n_entries"]
        mt_n = out["market_timing"]["n_echantillons"]
        print(f"brain_validation : rapport écrit (replay {mode} sur "
              f"{out['n_symbols']} symbole(s) + live {live_n} votes + "
              f"timing {mt_n} échantillons). "
              f"Agents battant le seuil déflaté (replay) : "
              f"{passed or 'aucun (données trop minces)'}. ADVISORY. VERDICT: SAFE")
    except Exception as exc:
        print(f"brain_validation : {type(exc).__name__}")


if __name__ == "__main__":
    main()
