"""Triage/priorisation du catalogue code base mql5. Python système, lecture seule.

Score = PERTINENCE (est-ce un signal directionnel tradeable ?) + NOUVEAUTÉ
(le bot ne l'a-t-il PAS déjà mesuré ?). Sort queue.json trié : les items en tête
sont les meilleurs candidats à RÉIMPLÉMENTER EN PYTHON puis passer au harness.

Aucun code tiers n'est téléchargé/exécuté : on ne score que titre + description.
"""
from __future__ import annotations
import json, re
from pathlib import Path

LAB = Path(__file__).resolve().parent
CAT = LAB / "catalog.json"
OUT = LAB / "queue.json"

# signal directionnel tradeable -> +
SIGNAL = ["indicator", "oscillator", "signal", "trend", "momentum", "breakout",
          "reversal", "divergence", "cycle", "filter", "entry", "regime",
          "volatility", "mean reversion", "predict", "forecast", "strength"]
# pas un signal (UI, gestion, utilitaire) -> -
NOISE = ["dashboard", "panel", "utility", "library", "export", "import", "manager",
         "copier", "converter", "alert", "notification", "gui", "interface",
         "button", "template", "money management", "lot", "risk manager", "news",
         "screenshot", "telegram", "email", "sound", "grid manager", "trade copier"]
# DÉJÀ couvert/mesuré par le bot -> pénalité nouveauté (avec le module concerné)
COVERED = {
    "rsi": "technicals", "ema": "technicals", "sma": "technicals", "macd": "classics",
    "stochastic": "technicals", "bollinger": "classics", "donchian": "classics",
    "vwap": "classics", "keltner": "classics", "ichimoku": "technicals",
    "adx": "technicals", "atr": "technicals", "cci": "technicals",
    "fractal": "geometric", "hurst": "geometric", "dfa": "geometric",
    "garch": "volatility", "entropy": "nolds", "lyapunov": "nolds",
    "neural": "nn", "machine learning": "nn", "lstm": "nn", "deep": "nn",
    "quantum": "qml", "sentiment": "sentiment", "funding": "carry",
    "order flow": "orderflow", "microstructure": "orderflow", "wavelet": "geometric",
}


def score(item):
    t = (item["title"] + " " + item.get("desc", "")).lower()
    sig = sum(1 for k in SIGNAL if k in t)
    noise = sum(1 for k in NOISE if k in t)
    covered = sorted({mod for k, mod in COVERED.items() if k in t})
    s = 2 * sig - 3 * noise - 2 * len(covered)
    return s, {"signal_kw": sig, "noise_kw": noise, "deja_couvert": covered}


def main():
    if not CAT.exists():
        print("catalog.json absent — lancer catalog.py (venv collecteur) d'abord.")
        return
    items = json.loads(CAT.read_text())
    scored = []
    for it in items:
        s, why = score(it)
        scored.append({**it, "score": s, "why": why})
    scored.sort(key=lambda x: -x["score"])
    OUT.write_text(json.dumps(scored, ensure_ascii=False, indent=1))
    print(f"{len(scored)} items triés -> queue.json")
    print("\n=== TOP candidats à réimplémenter + tester ===")
    for it in scored[:12]:
        cov = f" [déjà: {','.join(it['why']['deja_couvert'])}]" if it["why"]["deja_couvert"] else ""
        print(f"  score {it['score']:+3}  {it['title'][:70]}{cov}")
    print("\n=== rejetés (déjà couverts / non-signal) — extrait ===")
    for it in scored[-6:]:
        print(f"  score {it['score']:+3}  {it['title'][:70]}")


if __name__ == "__main__":
    main()
