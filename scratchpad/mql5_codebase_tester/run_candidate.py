"""Runner de l'agent testeur : teste un candidat réimplémenté via le harness,
imprime le rapport et JOURNALISE le verdict dans verdicts.jsonl.

    python3 run_candidate.py kalman_slope [SYM ...]

Symboles par défaut = ceux avec assez d'historique en cache (BTC/ETH sûrs).
"""
import json, sys, time
from pathlib import Path

import harness as H
from candidates import CANDIDATES

LAB = Path(__file__).resolve().parent
JOURNAL = LAB / "verdicts.jsonl"
DEFAULT_SYMS = ["BTCUSDT", "ETHUSDT"]


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CANDIDATES:
        print("candidats dispo :", ", ".join(CANDIDATES))
        return
    name = sys.argv[1]
    syms = [a for a in sys.argv[2:] if a.isupper()] or DEFAULT_SYMS
    fn, source = CANDIDATES[name]
    res = H.test_signal(fn, name, syms, h=1)
    H.print_report(res)
    verdict = {"candidat": name, "source_mql5": source, "symbols": syms,
               "n_configs": len(res["configs"]), "n_pass": res["n_pass"],
               "verdict": "EDGE" if res["n_pass"] >= max(2, len(res["configs"]) // 8) else "REJETÉ",
               "note": "passe si assez de configs franchissent la porte (net taker>0, t>=3), pas 1 isolée (bruit)"}
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(verdict, ensure_ascii=False) + "\n")
    print(f"\nVERDICT journalisé : {verdict['verdict']} "
          f"({res['n_pass']}/{len(res['configs'])} configs) -> verdicts.jsonl")


if __name__ == "__main__":
    main()
