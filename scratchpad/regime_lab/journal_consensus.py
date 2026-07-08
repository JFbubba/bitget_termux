"""
journal_consensus.py — edge conditionnel du CONSENSUS live (brain_log_history)
à 1 h, conditionné par le flag hmm2 CAUSAL construit sur les bougies 1H.

Limite annoncée d'avance : le journal ne couvre que quelques jours — trop court
pour des plis walk-forward ; on mesure UN SEUL bloc (le flag, lui, est ajusté
sur l'historique 1H STRICTEMENT antérieur au journal, puis filtré forward).
Résultat à lire comme un contrôle de cohérence, pas une preuve.

Lecture seule (journal + bougies). Écrit sa section dans resultats.json.
VERDICT: SAFE.
"""

import bisect
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
sys.path.insert(0, str(ICI.parent.parent))

import candles_history as ch                         # noqa: E402
import live_ic_audit as lia                          # noqa: E402
import regime_flags as rf                            # noqa: E402

HORIZON_S, TOL_S = 3600, 600
SORTIE = ICI / "resultats.json"


def fwd_par_symbole(entrees, sym):
    """[(ts, consensus, fwd_log)] pour un symbole (premier point >= ts+H, tol)."""
    seq = sorted((e for e in entrees if e.get("symbol") == sym
                  and e.get("consensus") is not None),
                 key=lambda e: e["ts"])
    out, j = [], 0
    for i, e in enumerate(seq):
        cible = e["ts"] + HORIZON_S
        j = max(j, i + 1)
        while j < len(seq) and seq[j]["ts"] < cible:
            j += 1
        if j >= len(seq) or seq[j]["ts"] - cible > TOL_S:
            continue
        try:
            out.append((e["ts"], float(e["consensus"]),
                        math.log(seq[j]["price"] / e["price"])))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return out


def flag_hmm2_causal(sym, ts_debut_journal):
    """{ts_ouverture_barre: flag} sur les bougies 1H : HMM fit sur les barres
    STRICTEMENT antérieures au journal, filtrage forward sur tout (causal)."""
    rows = ch.load(sym, "1H")
    if not rows:
        return None, None
    ts = np.array([r[0] / 1000.0 for r in rows])
    logp = rf.log_prices(np.array([float(r[4]) for r in rows]))
    obs = rf.log_returns(logp) * 100.0
    i_deb = int(np.searchsorted(ts, ts_debut_journal))
    if i_deb < 1000:
        return None, None
    m2 = rf.hmm_fit(obs[max(1, i_deb - 20000):i_deb], 2, seed=rf.SEED)
    if m2 is None:
        return None, None
    b0 = max(1, i_deb - 20000)
    a2 = rf.forward_filter(obs[b0:], m2)
    flags = (a2[:, 1] > 0.5).astype(int)             # 1 = haute vol
    return {float(ts[b0 + i]): int(flags[i]) for i in range(len(flags))}, ts[b0:]


def main():
    entrees = lia.charger_entrees()
    section = {"horizon_s": HORIZON_S, "n_entrees_journal": len(entrees),
               "avertissement": "journal peu profond (quelques jours), un seul "
                                "bloc — contrôle de cohérence, pas une preuve",
               "par_symbole": {}}
    if entrees:
        ts_all = [e["ts"] for e in entrees if e.get("ts")]
        t0, t1 = min(ts_all), max(ts_all)
        section["periode_journal"] = [
            time.strftime("%Y-%m-%d %H:%M", time.gmtime(t0)),
            time.strftime("%Y-%m-%d %H:%M", time.gmtime(t1))]
        section["profondeur_journal_jours"] = round((t1 - t0) / 86400, 2)
    for sym in ("BTCUSDT", "ETHUSDT"):
        ech = fwd_par_symbole(entrees, sym)
        if len(ech) < 100:
            section["par_symbole"][sym] = {"statut": f"{len(ech)} éch. (<100)"}
            continue
        t_deb = ech[0][0]
        fdict, ts_bars = flag_hmm2_causal(sym, t_deb)
        if not fdict:
            section["par_symbole"][sym] = {"statut": "flag 1H indisponible"}
            continue
        cles = sorted(fdict.keys())
        sig, fwd, flg = [], [], []
        for ts_e, c, f in ech:
            # dernière barre 1H FERMÉE au moment de l'entrée (ouverture + 3600 <= ts)
            i = bisect.bisect_right(cles, ts_e - 3600.0) - 1
            if i < 0 or ts_e - cles[i] > 3 * 3600:
                continue
            sig.append(c)
            fwd.append(f)
            flg.append(fdict[cles[i]])
        sig, fwd, flg = np.array(sig), np.array(fwd), np.array(flg)
        gp, gr = rf.ic_pair(sig, fwd, min_n=50)
        res = {"n": int(len(sig)), "ic_global": {"pearson": gp, "rang": gr}}
        # bascules sur la période du journal seulement
        cles_j = [c for c in cles if c >= t_deb - 3600]
        res["n_bascules_flag"] = int(np.sum(np.abs(np.diff(
            [fdict[c] for c in cles_j])))) if len(cles_j) > 1 else 0
        for v in (0, 1):
            m = flg == v
            if m.sum() >= 50:
                p, rg = rf.ic_pair(sig[m], fwd[m], min_n=50)
                res[f"regime_{v}"] = {"n": int(m.sum()), "pearson": p, "rang": rg}
            else:
                res[f"regime_{v}"] = {"n": int(m.sum()), "statut": "trop petit"}
        r0, r1 = res.get("regime_0", {}), res.get("regime_1", {})
        if r0.get("rang") is not None and r1.get("rang") is not None:
            res["delta_rang"] = r1["rang"] - r0["rang"]
        section["par_symbole"][sym] = res
    try:
        doc = json.loads(SORTIE.read_text(encoding="utf-8"))
    except Exception:
        doc = {}
    doc["journal_1h"] = section
    SORTIE.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(json.dumps(section, ensure_ascii=False, indent=1))
    print("FINI — section journal_1h écrite. Lecture seule, aucun ordre.")


if __name__ == "__main__":
    main()
