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
MIN_INTERVAL_H = 6.0


def _stale(now=None):
    """Le dernier rapport est-il assez vieux pour relancer ? (auto-throttle)."""
    try:
        age_h = ((time.time() if now is None else now) - REPORT_FILE.stat().st_mtime) / 3600.0
        return age_h >= MIN_INTERVAL_H
    except Exception:
        return True                                  # pas de rapport -> lancer


def build_output(symbol, ranked, live, now=None):
    """Assemble le rapport de validation (PUR, testable). 'live' = edge mesure sur les
    VOTES REELS journalises (brain_log, chemin 2) — ADDITIF / informatif : ne change PAS
    la decision de palier (qui lit 'ranking', le replay). Sert a comparer edge backtest
    vs edge live et a preparer une porte plus honnete (replay ET live)."""
    import agent_validation as av
    return {
        "generated_at": int(time.time() if now is None else now),
        "symbol": symbol,
        "ranking": ranked.get("agents", []),
        "deflation": ranked.get("deflation", {}),
        "weight_priors_advisory": av.suggest_weight_priors(ranked),
        "live": {"agents": (live or {}).get("agents", []),
                 "n_entries": (live or {}).get("n_entries", 0)},
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
        ranked = av.run(symbol)
        if ranked.get("error"):
            print(f"brain_validation indisponible : {ranked['error']}")
            return
        live = {}
        try:
            import swarm_brain
            live = av.evaluate_from_log(swarm_brain._read_log())   # chemin 2 : votes reels
        except Exception:
            live = {}
        out = build_output(symbol, ranked, live)
        REPORT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        passed = [a["agent"] for a in ranked.get("agents", []) if a.get("dsr", 0) >= 0.9]
        live_n = out["live"]["n_entries"]
        print(f"brain_validation : rapport écrit (replay + live, {live_n} votes journalisés). "
              f"Agents battant le seuil déflaté (replay) : "
              f"{passed or 'aucun (données trop minces)'}. ADVISORY. VERDICT: SAFE")
    except Exception as exc:
        print(f"brain_validation : {type(exc).__name__}")


if __name__ == "__main__":
    main()
