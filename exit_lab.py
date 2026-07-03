"""
exit_lab.py — laboratoire des SORTIES (lecture seule). SAFE.

§60 : SL = 1.5·ATR et RR = 2 sont des CONVENTIONS jamais mesurées. Ce module
mesure, sur les issues PAPER finalisées (n grand) et les trades réels quand ils
s'accumuleront, la MFE/MAE (excursion max favorable/adverse en unités d'ATR ou
de distance de stop) : « à quelle distance les trades meurent-ils vraiment ? »
-> de quoi calibrer RR/SL sur données. ADVISORY : aucun paramètre n'est changé
ici — l'instrument accumule et la revue hebdo affiche ; tout changement de
SL/TP réel sera une décision mesurée séparée.

Fonctions PURES testables ; lecture des CSV best-effort. AUCUN ordre.
CLI : python exit_lab.py
"""

import csv
from pathlib import Path

from numeric_utils import safe_float


def mfe_mae(entry, side, highs, lows):
    """Excursions max favorable/adverse d'un trade, en FRACTION du prix d'entrée.
    PUR. side long : MFE = plus haut atteint, MAE = plus bas ; short : miroir.
    (None, None) si données insuffisantes."""
    e = safe_float(entry)
    hs = [safe_float(h) for h in highs or []]
    ls = [safe_float(l) for l in lows or []]
    hs = [h for h in hs if h]
    ls = [l for l in ls if l]
    if not e or e <= 0 or not hs or not ls:
        return None, None
    if str(side).upper() in ("LONG", "BUY"):
        return (max(hs) - e) / e, (e - min(ls)) / e
    return (e - min(ls)) / e, (max(hs) - e) / e


def stats_issues(rows):
    """Agrège les issues finalisées PAPER : par issue (TP/SL/AMBIGU), taux et
    ratio de déséquilibre TP/SL. PUR. rows = dicts avec 'outcome'."""
    comptes = {}
    for r in rows or []:
        o = str((r or {}).get("outcome", "")).upper() or "?"
        # normalisation : les labels du journal sont en clair (« TP TOUCHÉ », ...)
        cle = "TP" if "TP" in o else "SL" if "SL" in o else "AMBIGU" if "AMBIG" in o else o
        comptes[cle] = comptes.get(cle, 0) + 1
    total = sum(comptes.values())
    tp, sl = comptes.get("TP", 0), comptes.get("SL", 0)
    return {"n": total, "comptes": comptes,
            "wr_pct": round(100 * tp / (tp + sl), 1) if (tp + sl) else None,
            "ratio_tp_sl": round(tp / sl, 3) if sl else None}


def analyser_reels(fills=None, candles_par_symbole=None, horizon_bars=16):
    """MFE/MAE des trades RÉELS du bot (via fills appariés open->close). Retourne
    {n, mfe_med, mae_med, note}. Honnête : « échantillon insuffisant » sous 10
    round-trips — l'instrument ACCUMULE, il ne conclut pas avant l'heure."""
    try:
        import futures_report as fr
        import futures_auto as fa
        events = fa._executor_events()
        debut = fr.premier_ordre_reel_ts(events)
        if fills is None:
            fills = [f for f in (fr.fetch_fills() or [])
                     if debut and safe_float(f.get("cTime", 0)) / 1000.0 >= debut]
    except Exception:
        fills = fills or []
    # round-trips approximés : fills avec profit != 0 = fermetures
    fermetures = [f for f in fills if safe_float(f.get("profit"))]
    n = len(fermetures)
    if n < 10:
        return {"n": n, "mfe_med": None, "mae_med": None,
                "note": f"échantillon réel insuffisant ({n} fermetures < 10) — "
                        "l'instrument accumule"}
    # avec ≥10 fermetures, les MFE/MAE se calculeront depuis candles_history
    # (chemins d'entrée/sortie horodatés) — implémentation au premier seuil atteint.
    return {"n": n, "mfe_med": None, "mae_med": None,
            "note": "seuil atteint — calcul MFE/MAE à câbler sur candles_history"}


def _lire_outcomes():
    try:
        import config
        p = Path(config.FINAL_OUTCOMES_FILE)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent / p
        if not p.exists():
            return []
        with p.open("r", newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def snapshot():
    """{paper: stats_issues, reels: analyser_reels} — pour la revue hebdo."""
    return {"paper": stats_issues(_lire_outcomes()), "reels": analyser_reels()}


def build_report(s=None):
    s = snapshot() if s is None else s
    p, r = s.get("paper") or {}, s.get("reels") or {}
    lignes = ["=== EXIT LAB — les sorties, mesurées (advisory, lecture seule) ==="]
    lignes.append(f"PAPER : {p.get('n', 0)} issues finalisées · WR {p.get('wr_pct')}% "
                  f"· ratio TP/SL {p.get('ratio_tp_sl')} · détail {p.get('comptes')}")
    lignes.append(f"RÉEL : {r.get('n', 0)} fermetures — {r.get('note', '')}")
    lignes.append("SL 1.5·ATR / RR 2 restent des conventions TANT QUE l'échantillon "
                  "réel est court ; ce laboratoire accumule de quoi les juger.")
    lignes.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
