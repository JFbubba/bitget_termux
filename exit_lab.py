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


def paires_reelles(events):
    """PUR. Apparie les ordres RÉELS du ledger en ROUND-TRIPS :
    [(symbol, side, entry, sl, ts_open, ts_close)]. Une ouverture (non-reduce)
    est fermée par le premier reduce du même (symbol, side) qui la suit ;
    les ouvertures encore vivantes sont ignorées."""
    ouverts = {}
    paires = []
    for e in sorted(events or [], key=lambda x: x.get("ts", 0)):
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        o = e.get("order") or {}
        cle = (str(o.get("symbol") or "BTCUSDT").upper(), str(o.get("side")))
        if o.get("reduce"):
            ouv = ouverts.pop(cle, None)
            if ouv:
                paires.append((cle[0], cle[1], ouv["entry"], ouv.get("sl"),
                               ouv["ts"], e.get("ts")))
        else:
            entry = safe_float(o.get("entry"))
            if entry:
                ouverts[cle] = {"entry": entry, "sl": safe_float(o.get("stop_loss")),
                                "ts": e.get("ts")}
    return paires


def _ts_sec(brut):
    """Timestamp de bougie en SECONDES quelle que soit la source :
    ms.candles émet des secondes, candles_history des millisecondes. PUR."""
    t = safe_float(brut) or 0.0
    return t / 1000.0 if t > 1e12 else t


def fenetre_bougies(rows, ts_debut, ts_fin):
    """PUR. Bougies dont l'intervalle [ts, ts+1h] recouvre [ts_debut, ts_fin],
    unités normalisées via _ts_sec."""
    return [r for r in rows or []
            if ts_debut - 3600 <= _ts_sec(r[0]) <= ts_fin]


def _candles_fenetre(symbol, ts_debut, ts_fin):
    """Bougies 1h couvrant [ts_debut, ts_fin] (fraîches d'abord, repli historique)."""
    try:
        import market_sources as ms
        rows = ms.candles(symbol, "1h", 400) or []
    except Exception:
        rows = []
    if not rows or _ts_sec(rows[0][0]) > ts_debut:
        try:
            import candles_history as ch
            rows = ch.load(symbol, "1h") or rows
        except Exception:
            pass
    return fenetre_bougies(rows, ts_debut, ts_fin)


def analyser_reels(events=None, fenetres=None):
    """MFE/MAE des ROUND-TRIPS RÉELS (§63 : câblé, plus de stub). Retourne
    {n, mfe_med_pct, mae_med_pct, mfe_r_med, note} — les _r sont en unités de
    DISTANCE DE STOP (R) quand le SL de l'ordre est connu. Honnête : les
    médianes s'affichent dès la 1re paire, le verdict attend n >= 10."""
    try:
        if events is None:
            import futures_auto as fa
            events = fa._executor_events()
    except Exception:
        events = events or []
    paires = paires_reelles(events)
    mfes, maes, mfes_r = [], [], []
    for sym, side, entry, sl, t0, t1 in paires:
        rows = (fenetres or {}).get((sym, t0)) if fenetres else _candles_fenetre(sym, t0, t1)
        if not rows:
            continue
        mfe, mae = mfe_mae(entry, side, [r[2] for r in rows], [r[3] for r in rows])
        if mfe is None:
            continue
        mfes.append(mfe)
        maes.append(mae)
        if sl and entry:
            r_dist = abs(entry - sl) / entry
            if r_dist > 1e-6:
                mfes_r.append(mfe / r_dist)
    n = len(mfes)
    if n == 0:
        return {"n": 0, "mfe_med_pct": None, "mae_med_pct": None, "mfe_r_med": None,
                "note": "aucun round-trip réel mesurable encore"}
    import statistics
    out = {"n": n,
           "mfe_med_pct": round(100 * statistics.median(mfes), 3),
           "mae_med_pct": round(100 * statistics.median(maes), 3),
           "mfe_r_med": round(statistics.median(mfes_r), 2) if mfes_r else None}
    out["note"] = (f"{n} round-trips · MFE méd {out['mfe_med_pct']}% · MAE méd "
                   f"{out['mae_med_pct']}%"
                   + (f" · MFE {out['mfe_r_med']}R" if out["mfe_r_med"] else "")
                   + ("" if n >= 10 else f" — verdict à n>=10 ({n}/10)"))
    return out


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
