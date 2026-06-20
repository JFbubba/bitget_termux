"""
stats_report.py — statistiques LECTURE SEULE des résultats finalisés.

Classement : SAFE.
  - lit uniquement final_outcomes_journal.csv (donnees deja journalisees)
  - aucun reseau, aucun appel API, aucun ordre, aucun secret
  - stdlib uniquement (pas de requests)

Calcule, a partir des outcomes finalises (TP TOUCHE / SL TOUCHE / AMBIGU) :
  - taux de reussite global = TP / (TP + SL)
  - ratio TP/SL
  - repartition par symbole
  - repartition par sens (LONG / SHORT)

Commande Telegram associee : /stats
Usage CLI :
    python stats_report.py
"""

import csv
from pathlib import Path

import config

FINAL_FILE = Path(config.FINAL_OUTCOMES_FILE)

FINAL_OUTCOMES = {"TP TOUCHÉ", "SL TOUCHÉ", "AMBIGU"}
WIN = "TP TOUCHÉ"
LOSS = "SL TOUCHÉ"


def _win_rate(tp, sl):
    """Taux de reussite en % sur les seuls TP+SL (AMBIGU exclu). None si vide."""
    total = tp + sl
    return (tp / total * 100.0) if total else None


def compute_stats(rows):
    """Agrege une liste de lignes (dict) en statistiques. Fonction pure."""
    stats = {
        "total": 0,
        "tp": 0,
        "sl": 0,
        "ambigu": 0,
        "by_symbol": {},
        "by_side": {},
    }

    for row in rows:
        outcome = (row.get("outcome") or "").strip()
        if outcome not in FINAL_OUTCOMES:
            continue

        symbol = (row.get("symbol") or "?").strip() or "?"
        side = (row.get("side") or "?").strip().upper() or "?"
        bucket = "tp" if outcome == WIN else "sl" if outcome == LOSS else "ambigu"

        stats["total"] += 1
        stats[bucket] += 1
        stats["by_symbol"].setdefault(symbol, {"tp": 0, "sl": 0, "ambigu": 0})[bucket] += 1
        stats["by_side"].setdefault(side, {"tp": 0, "sl": 0, "ambigu": 0})[bucket] += 1

    stats["win_rate"] = _win_rate(stats["tp"], stats["sl"])
    stats["tp_sl_ratio"] = (stats["tp"] / stats["sl"]) if stats["sl"] else None
    return stats


def _fmt_rate(rate):
    return "n/a" if rate is None else f"{rate:.1f}%"


def build_report(stats):
    """Formate les stats en texte lisible (Telegram / CLI). Aucun secret."""
    lines = ["=== STATS (paper / dry-run) ==="]

    if stats["total"] == 0:
        lines.append("Aucun résultat finalisé pour l'instant.")
        lines.append("")
        lines.append("Mode: lecture seule. Aucun ordre réel. VERDICT: SAFE")
        return "\n".join(lines)

    ratio = stats["tp_sl_ratio"]
    lines.append(
        f"Finalisés  : {stats['total']} "
        f"(TP {stats['tp']} | SL {stats['sl']} | AMBIGU {stats['ambigu']})"
    )
    lines.append(f"Réussite   : {_fmt_rate(stats['win_rate'])}  (TP / (TP+SL))")
    lines.append(f"Ratio TP/SL: {'n/a' if ratio is None else f'{ratio:.2f}'}")
    lines.append("")

    lines.append("Par symbole:")
    for symbol in sorted(stats["by_symbol"]):
        b = stats["by_symbol"][symbol]
        wr = _win_rate(b["tp"], b["sl"])
        lines.append(
            f"- {symbol:<10} TP {b['tp']} | SL {b['sl']} | AMB {b['ambigu']} | {_fmt_rate(wr)}"
        )
    lines.append("")

    lines.append("Par sens:")
    for side in sorted(stats["by_side"]):
        b = stats["by_side"][side]
        wr = _win_rate(b["tp"], b["sl"])
        lines.append(
            f"- {side:<6} TP {b['tp']} | SL {b['sl']} | AMB {b['ambigu']} | {_fmt_rate(wr)}"
        )
    lines.append("")

    lines.append("Mode: lecture seule. Aucun ordre réel. VERDICT: SAFE")
    return "\n".join(lines)


def load_rows(path=FINAL_FILE):
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        return list(csv.DictReader(f))


def main():
    print(build_report(compute_stats(load_rows())))


if __name__ == "__main__":
    main()
